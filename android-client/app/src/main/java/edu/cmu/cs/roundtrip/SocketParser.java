package edu.cmu.cs.roundtrip;

import java.util.Optional;

public class SocketParser {
    static Optional<String> getIpAddress(String socket) {
        int colon_pos = socket.indexOf(':');
        if (colon_pos == -1) {
            return Optional.empty();
        }
        return Optional.of(socket.substring(0, colon_pos));
    }

    static Optional<String> getPort(String socket) {
        int colon_pos = socket.indexOf(':');
        if (colon_pos == -1) {
            return Optional.empty();
        }
        return Optional.of(socket.substring(colon_pos + 1));
    }
}
