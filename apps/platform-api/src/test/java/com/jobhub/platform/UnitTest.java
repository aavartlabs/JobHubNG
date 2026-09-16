package com.jobhub.platform;

import com.jobhub.platform.config.CorsConfig;
import com.jobhub.platform.config.JacksonConfig;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.assertThat;

class UnitTest {

    @Test
    void corsConfig_canBeCreated() {
        assertThat(new CorsConfig()).isNotNull();
    }

    @Test
    void jacksonConfig_canBeCreated() {
        assertThat(new JacksonConfig()).isNotNull();
    }

    @Test
    void objectMapper_canBeCreated() {
        assertThat(new ObjectMapper()).isNotNull();
    }

    @Test
    void passwordEncoder_works() {
        var encoder = new org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder();
        String hash = encoder.encode("test123");
        assertThat(encoder.matches("test123", hash)).isTrue();
        assertThat(encoder.matches("wrong", hash)).isFalse();
    }
}
