package edu.cmu.cs.roundtrip;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Toast;

import androidx.annotation.Nullable;

public class ServerConfigActivity extends Activity {
    @Override
    protected void onCreate(@Nullable Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        setContentView(R.layout.server_config);

        Button submitButton = findViewById(R.id.submitServerIPButton);
        EditText textBox = findViewById(R.id.ServerIPAddressTextBox);

        submitButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                String server_ip = textBox.getText().toString();
                if (SocketParser.getPort(server_ip).isPresent() &&
                        SocketParser.getIpAddress(server_ip).isPresent()) {
                    Intent i = new Intent(ServerConfigActivity.this, GabrielActivity.class);
                    i.putExtra("server_ip", server_ip);
                    startActivity(i);
                } else {
                    Toast.makeText(ServerConfigActivity.this, "Invalid server IP. Enter \"hostname:port\"", Toast.LENGTH_SHORT).show();
                }
            }
        });

    }
}
