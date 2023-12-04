package edu.cmu.cs.roundtrip;

import android.Manifest;
import android.annotation.SuppressLint;
import android.content.IntentSender;
import android.content.pm.PackageManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.Bundle;
import android.os.Looper;
import android.speech.tts.TextToSpeech;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.result.ActivityResultCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.camera.core.ImageAnalysis;
import androidx.camera.core.ImageProxy;
import androidx.camera.view.PreviewView;
import androidx.core.app.ActivityCompat;

import com.google.android.gms.common.api.ResolvableApiException;
import com.google.android.gms.location.FusedLocationProviderClient;
import com.google.android.gms.location.LocationCallback;
import com.google.android.gms.location.LocationRequest;
import com.google.android.gms.location.LocationResult;
import com.google.android.gms.location.LocationServices;
import com.google.android.gms.location.LocationSettingsRequest;
import com.google.android.gms.location.LocationSettingsResponse;
import com.google.android.gms.location.Priority;
import com.google.android.gms.tasks.OnFailureListener;
import com.google.android.gms.tasks.OnSuccessListener;
import com.google.android.gms.tasks.Task;
import com.google.protobuf.Any;
import com.google.protobuf.ByteString;

import java.time.Duration;
import java.time.Instant;
import java.util.Locale;
import java.util.Map;
import java.util.function.Consumer;

import edu.cmu.cs.gabriel.camera.CameraCapture;
import edu.cmu.cs.gabriel.camera.YuvToJPEGConverter;
import edu.cmu.cs.gabriel.client.comm.ServerComm;
import edu.cmu.cs.gabriel.client.results.ErrorType;
import edu.cmu.cs.gabriel.protocol.Protos;
import edu.cmu.cs.gabriel.protocol.Protos.InputFrame;
import edu.cmu.cs.gabriel.protocol.Protos.PayloadType;
import edu.cmu.cs.gabriel.protocol.Protos.ResultWrapper;
import edu.cmu.cs.roundtrip.protos.ClientExtras;

public class GabrielActivity extends AppCompatActivity {
    private static final String TAG = "GabrielActivity";
    private static final String SOURCE = "roundtrip";
    private static final int PORT = 8099;
    private static final int WIDTH = 768;
    private static final int HEIGHT = 1024;
    private static final int PERMISSION_REQUEST_LOCATION = 42;

    private ServerComm serverComm;
    private YuvToJPEGConverter yuvToJPEGConverter;
    private CameraCapture cameraCapture;

    private TextView textView = null;

    private EditText editText = null;

    private PreviewView previewView = null;

    private String typed_string = "";

    private Instant annotation_display_start = null;

    private TextToSpeech tts;

    private long prev_time = 0;

    private String prev_spoken = "";

    private LocationManager locationManager;

    private LocationListener listener;

    private FusedLocationProviderClient fusedLocationProviderClient;

    private LocationRequest locationRequest;

    private LocationCallback locationCallback;

    private double currLatitude = 0;
    private double currLongitude = 0;

//    @SuppressLint("MissingPermission")
//    @Override
//    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
//        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
//        if (requestCode == PERMISSION_REQUEST_LOCATION) {
//            if (grantResults.length == 1 && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
//                Log.i(TAG, "Location services granted");
//            } else {
//                Toast.makeText(this, "Location permissions are required for annotations", Toast.LENGTH_SHORT).show();
//            }
//        } else {
//            Log.i(TAG, Integer.toString(requestCode));
//        }
//    }

    @Override
    protected void onPause() {
        super.onPause();
        Log.i(TAG, "Pausing location updates");
        fusedLocationProviderClient.removeLocationUpdates(locationCallback);
    }

    @Override
    protected void onResume() {
        super.onResume();
        startLocationUpdates();
    }

    @SuppressLint("MissingPermission")
    private void startLocationUpdates() {
        Log.i(TAG, "Requesting location updates");
        fusedLocationProviderClient.requestLocationUpdates(
                locationRequest, locationCallback, Looper.getMainLooper());
    }
    private void setupLocationUpdates() {
        locationCallback = new LocationCallback() {
            @Override
            public void onLocationResult(@NonNull LocationResult locationResult) {
                super.onLocationResult(locationResult);
                Location location = locationResult.getLastLocation();
                assert location != null;
                currLatitude = location.getLatitude();
                currLongitude = location.getLongitude();
                Log.i(TAG, "latitude: " + Double.toString(currLatitude) + " longitude: " + Double.toString(currLongitude));
            }
        };

        locationRequest = new LocationRequest.Builder(
                Priority.PRIORITY_HIGH_ACCURACY, 1000)
                .build();
        LocationSettingsRequest.Builder locationSettingsBuilder = new LocationSettingsRequest.Builder()
                .addLocationRequest(locationRequest);
        Task<LocationSettingsResponse> result =
                LocationServices.getSettingsClient(this).checkLocationSettings(
                        locationSettingsBuilder.build());
        result.addOnSuccessListener(this, new OnSuccessListener<LocationSettingsResponse>() {
            @Override
            public void onSuccess(LocationSettingsResponse locationSettingsResponse) {
            }
        });

        result.addOnFailureListener(this, new OnFailureListener() {
            @Override
            public void onFailure(@NonNull Exception e) {
                Log.i(TAG, "Failed to get correct locating settings set up");
                if (e instanceof ResolvableApiException) {
                    try {
                        ResolvableApiException resolvable = (ResolvableApiException) e;
                        resolvable.startResolutionForResult(GabrielActivity.this, 42);
                    } catch (IntentSender.SendIntentException ex) {
                        throw new RuntimeException(ex);
                    }
                }
            }
        });

    }
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        setContentView(R.layout.activity_gabriel);

        previewView = findViewById(R.id.preview);
        textView = findViewById(R.id.textAnnotation);
        editText = findViewById(R.id.editText);

        Button button = findViewById(R.id.startAnnotationButton);
        prev_time = System.currentTimeMillis();

        fusedLocationProviderClient = LocationServices.getFusedLocationProviderClient(this);

        tts = new TextToSpeech(this, new TextToSpeech.OnInitListener() {
            @Override
            public void onInit(int status) {
                if (status == TextToSpeech.SUCCESS) {
                    int result = tts.setLanguage(Locale.US);

                    if (result == TextToSpeech.LANG_MISSING_DATA ||
                            result == TextToSpeech.LANG_NOT_SUPPORTED) {
                        Log.e("TTS", "Language not supported");
                    } else {
                        // The TTS engine has been successfully initialized
                        // You can now use textToSpeech.speak(...)
                    }
                } else {
                    Log.e("TTS", "Initialization failed");
                }
            }
        });

        Consumer<ResultWrapper> consumer = resultWrapper -> {
            if (resultWrapper.getResultsCount() == 0) {
                if (annotation_display_start != null &&
                        Duration.between(annotation_display_start, Instant.now()).getSeconds() > 1) {
                    textView.setText("");
                }
                return;
            }
            ResultWrapper.Result result = resultWrapper.getResults(0);
            ByteString byteString = result.getPayload();
            textView.setText(byteString.toStringUtf8());
            annotation_display_start = Instant.now();
            String to_speak = byteString.toStringUtf8();
            if (!tts.isSpeaking()) {
                if (prev_spoken.equals(to_speak)) {
                    // Same annotation, don't repeat if within 5 seconds
                    long curr_time = System.currentTimeMillis();
                    if (curr_time - prev_time > 5000) {
                        prev_time = curr_time;
                        tts.speak(to_speak, TextToSpeech.QUEUE_FLUSH, null, null);
                    }
                } else {
                    // Different annotation, speak immediately
                    prev_spoken = to_speak;
                    tts.speak(to_speak, TextToSpeech.QUEUE_FLUSH, null, null);

                }
            }
        };

        Consumer<ErrorType> onDisconnect = errorType -> {
            Log.e(TAG, "Disconnect Error:" + errorType.name());
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    Toast.makeText(GabrielActivity.this, "Could not connect to server", Toast.LENGTH_SHORT).show();
                }
            });
            finish();
        };

        Bundle extras = getIntent().getExtras();
        String socket = extras.getString("server_ip");
        String host = SocketParser.getIpAddress(socket).get();
        String port = SocketParser.getPort(socket).get();
        Log.i(TAG, "Connecting to server at " + host + ":" + port);

        serverComm = ServerComm.createServerComm(
                consumer, host, Integer.parseInt(port), getApplication(), onDisconnect);

        yuvToJPEGConverter = new YuvToJPEGConverter(this);

        setupLocationUpdates();
        maybeRequestPermissions();

        // Set a click listener on the button
        button.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                typed_string = editText.getText().toString();
                editText.getText().clear();
                Toast.makeText(GabrielActivity.this, "Sending annotation to server", Toast.LENGTH_SHORT).show();
            }
        });
        editText.setOnFocusChangeListener(new View.OnFocusChangeListener() {
            @Override
            public void onFocusChange(View view, boolean b) {
                String default_string = getString(R.string.annotation_text_box_default_val);
                if (!b && editText.getText().toString().isEmpty()) {
                    editText.setText(default_string);
                    return;
                }
                if (b && editText.getText().toString().equals(default_string)) {
                    editText.setText("");
                }
            }
        });
    }
    private void maybeRequestPermissions() {
        if (ActivityCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) !=
                PackageManager.PERMISSION_GRANTED || ActivityCompat.checkSelfPermission
                (this, Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED ||
                ActivityCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            Log.i(TAG, "Requesting permissions for camera & location");

            ActivityResultCallback<Map<String, Boolean>> activityResultCallback = result -> {
                Boolean fineLocationGranted = result.getOrDefault(Manifest.permission.ACCESS_FINE_LOCATION, false);
                Boolean coarseLocationGranted = result.getOrDefault(Manifest.permission.ACCESS_COARSE_LOCATION, false);
                Boolean cameraGranted = result.getOrDefault(Manifest.permission.CAMERA, false);
                if (fineLocationGranted == null || !fineLocationGranted) {
                    Toast.makeText(GabrielActivity.this, "Fine location access is required", Toast.LENGTH_LONG).show();
                } else if (cameraGranted == null || !cameraGranted) {
                    Toast.makeText(GabrielActivity.this, "Camera access is required", Toast.LENGTH_LONG).show();
                } else {
                    Log.i(TAG, "Location and camera access granted");
                    startLocationUpdates();
                    cameraCapture = new CameraCapture(GabrielActivity.this, analyzer, WIDTH, HEIGHT, previewView);
                }
            };
            ActivityResultLauncher<String[]> locationPermissionRequest = registerForActivityResult(
                    new ActivityResultContracts.RequestMultiplePermissions(), activityResultCallback);
            locationPermissionRequest.launch(new String[] {
                    Manifest.permission.ACCESS_FINE_LOCATION,
                    Manifest.permission.ACCESS_COARSE_LOCATION,
                    Manifest.permission.CAMERA
            });
        } else {
            Log.i(TAG, "Location and camera access already provided");
            startLocationUpdates();
            cameraCapture = new CameraCapture(GabrielActivity.this, analyzer, WIDTH, HEIGHT, previewView);
        }
    }

    final private ImageAnalysis.Analyzer analyzer = new ImageAnalysis.Analyzer() {
        @Override
        public void analyze(@NonNull ImageProxy image) {
            serverComm.sendSupplier(() -> {
                ByteString jpegByteString = yuvToJPEGConverter.convert(image);

                Protos.InputFrame.Builder inputFrameBuilder = InputFrame.newBuilder()
                        .setPayloadType(PayloadType.IMAGE)
                        .addPayloads(jpegByteString);

                ClientExtras.Location currentLocation =
                        ClientExtras.Location.newBuilder()
                                .setLatitude(currLatitude)
                                .setLongitude(currLongitude)
                                .build();
                ClientExtras.Extras.Builder extrasBuilder =
                        ClientExtras.Extras.newBuilder()
                                .setCurrentLocation(currentLocation);
                if (!typed_string.isEmpty()) {
                    extrasBuilder.setAnnotationText(typed_string);
                    typed_string = "";
                }
                ClientExtras.Extras extras = extrasBuilder.build();
                Any any = Any.newBuilder()
                        .setValue(extras.toByteString())
                        .setTypeUrl("type.googleapis.com/client.Extras")
                        .build();
                inputFrameBuilder.setExtras(any);
                return inputFrameBuilder.build();
            }, SOURCE, false);

            image.close();
        }
    };

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (tts != null) {
            tts.stop();
            tts.shutdown();
        }
        cameraCapture.shutdown();
    }
}
