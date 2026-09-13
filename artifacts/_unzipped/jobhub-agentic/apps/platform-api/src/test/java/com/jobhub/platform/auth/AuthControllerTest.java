package com.jobhub.platform.auth;

import org.junit.jupiter.api.Test;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.assertj.core.api.Assertions.assertThat;

class AuthControllerTest {
    @Test void passwordEncoderCanVerifyDemoPassword() {
        var encoder = new BCryptPasswordEncoder();
        String hash = encoder.encode("password");
        assertThat(encoder.matches("password", hash)).isTrue();
        assertThat(encoder.matches("wrong", hash)).isFalse();
    }
}
