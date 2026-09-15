package com.jobhub.platform.controller;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1")
public class PlatformController {

    @GetMapping("/admin/dataflow")
    @PreAuthorize("hasAuthority('ADMIN_DATAFLOW_READ')")
    public String dataflow() {
        return "{\"status\": \"ok\", \"services\": [\"platform-api\", \"web\"]}";
    }

    @GetMapping("/ops/health")
    public String health() {
        return "{\"service\": \"platform-api\", \"phase\": \"1.0\", \"status\": \"READY\"}";
    }
}
