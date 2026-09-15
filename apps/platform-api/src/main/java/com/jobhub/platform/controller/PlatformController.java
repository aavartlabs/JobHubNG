package com.jobhub.platform.controller;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
public class PlatformController {

    @GetMapping("/ops/health")
    public String health() {
        return "{\"service\": \"platform-api\", \"phase\": \"1.0\", \"status\": \"READY\"}";
    }
}
