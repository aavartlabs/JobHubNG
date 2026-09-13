package com.jobhub.platform.common;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public final class JsonSupport {
    private JsonSupport() {}
    public static String write(ObjectMapper mapper, Object value) {
        try { return mapper.writeValueAsString(value); }
        catch (JsonProcessingException e) { throw new IllegalStateException("JSON serialization failed", e); }
    }
}
