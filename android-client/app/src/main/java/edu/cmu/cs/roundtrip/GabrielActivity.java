package edu.cmu.cs.roundtrip;

import android.Manifest;
import android.annotation.SuppressLint;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.hardware.Camera;
import android.hardware.Sensor;
import android.hardware.SensorManager;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.media.AudioRecord;
import android.os.Bundle;
import android.provider.Settings;
import android.speech.tts.TextToSpeech;

import java.util.Locale;

import android.text.Editable;
import android.text.TextWatcher;
import android.util.Log;
import android.view.MotionEvent;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.MediaController;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.camera.core.ImageAnalysis;
import androidx.camera.core.ImageProxy;
import androidx.camera.view.PreviewView;
import androidx.core.app.ActivityCompat;

import com.google.protobuf.Any;
import com.google.protobuf.ByteString;

import java.io.ByteArrayOutputStream;
import java.time.Duration;
import java.time.Instant;
import java.util.function.Consumer;

import edu.cmu.cs.gabriel.camera.CameraCapture;
import edu.cmu.cs.gabriel.camera.YuvToJPEGConverter;
import edu.cmu.cs.gabriel.camera.ImageViewUpdater;
import edu.cmu.cs.gabriel.client.comm.ServerComm;
import edu.cmu.cs.gabriel.client.results.ErrorType;
import edu.cmu.cs.gabriel.protocol.Protos;
import edu.cmu.cs.gabriel.protocol.Protos.InputFrame;
import edu.cmu.cs.gabriel.protocol.Protos.ResultWrapper;
import edu.cmu.cs.gabriel.protocol.Protos.PayloadType;
import edu.cmu.cs.roundtrip.protos.ClientExtras;

public class GabrielActivity extends AppCompatActivity {
    private static final String TAG = "GabrielActivity";
    private static final String SOURCE = "roundtrip";
    private static final int PORT = 8099;
    private static final int WIDTH = 768;
    private static final int HEIGHT = 1024;

    private ServerComm serverComm;
    private YuvToJPEGConverter yuvToJPEGConverter;
    private CameraCapture cameraCapture;

    private TextView textView = null;

    private EditText editText = null;

    private String typed_string = "";

    private Instant annotation_display_start = null;

    private TextToSpeech tts;

    private long prev_time = 0;

    private String prev_spoken = "";


    private LocationManager locationManager;

    private double currLatitude = 0;
    private double currLongitude = 0;

    private LocationListener listener = null;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        setContentView(R.layout.activity_gabriel);

        PreviewView previewView = findViewById(R.id.preview);
        textView = findViewById(R.id.textAnnotation);
        editText = findViewById(R.id.editText);
        Button button = findViewById(R.id.startAnnotationButton);

        prev_time = System.currentTimeMillis();
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
        cameraCapture = new CameraCapture(this, analyzer, WIDTH, HEIGHT, previewView);

        // Set a click listener on the button
        button.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                typed_string = editText.getText().toString();
                editText.getText().clear();

                textView.setText("currLatitude: "+(int)currLatitude+ "currLongitude: "+(int)currLongitude);
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

    @Override
    protected void onStart() {
        super.onStart();

        // This verification should be done during onStart() because the system calls
        // this method when the user returns to the activity, which ensures the desired
        // location provider is enabled each time the activity resumes from the stopped state.
        locationManager =
                (LocationManager) getSystemService(Context.LOCATION_SERVICE);
        final boolean locEnabled = locationManager.isProviderEnabled(LocationManager.NETWORK_PROVIDER);

        listener = new LocationListener() {

            @Override
            public void onLocationChanged(Location location) {
                // A new location update is received.  Do something useful with it.  In this case,
                // we're sending the update to a handler which then updates the UI with the new
                // location.

                currLatitude = location.getLatitude();
                currLongitude = location.getLongitude();

            }

            @Override
            public void onStatusChanged(String s, int i, Bundle bundle) {

            }

            @Override
            public void onProviderEnabled(String s) {

            }

            @Override
            public void onProviderDisabled(String s) {

            }

        };


        if (!locEnabled) {
            // Build an alert dialog here that requests that the user enable
            // the location services, then when the user clicks the "OK" button,
            // call enableLocationSettings()
            enableLocationSettings();
        } else {

            if (ActivityCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) !=
                    PackageManager.PERMISSION_GRANTED && ActivityCompat.checkSelfPermission
                    (this, Manifest.permission.ACCESS_COARSE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                // Seems IDE requires to add this check, but we've taken care of this
                return;
            }
            locationManager.requestLocationUpdates(LocationManager.NETWORK_PROVIDER,
                    10000,          // 10-second interval.
                    0,             // 10 meters.
                    listener);
        }



    }

    private void enableLocationSettings() {
        Intent settingsIntent = new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS);
        startActivity(settingsIntent);
    }
    final private ImageAnalysis.Analyzer analyzer = new ImageAnalysis.Analyzer() {
        @Override
        public void analyze(@NonNull ImageProxy image) {
            serverComm.sendSupplier(() -> {
                ByteString jpegByteString = yuvToJPEGConverter.convert(image);

                Protos.InputFrame.Builder builder = InputFrame.newBuilder()
                        .setPayloadType(PayloadType.IMAGE)
                        .addPayloads(jpegByteString);

                if (!typed_string.isEmpty()) {
                    // TODO: Send currLatitude and currLongitude to server
                    ClientExtras.AnnotationData annotationData =
                            ClientExtras.AnnotationData.newBuilder()
                                    .setAnnotationText(typed_string)
                                    .setFrameData(jpegByteString)
                                    .build();
                    Any any = Any.newBuilder()
                            .setValue(annotationData.toByteString())
                            .setTypeUrl("type.googleapis.com/client.AnnotationData")
                            .build();
                    builder.setExtras(any);
                    typed_string = "";
                }
                return builder.build();
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
