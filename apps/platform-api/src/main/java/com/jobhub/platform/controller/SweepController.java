package com.jobhub.platform.controller;

import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/admin/sweep")
@RequiredArgsConstructor
public class SweepController {

    @GetMapping("/status")
    public Map<String, Object> status() {
        return Map.of(
            "status", "READY",
            "lastSweep", "2026-09-16T09:12:00Z",
            "sources", Map.of(
                "linkedin", Map.of("status", "OK", "jobs", 4521),
                "indeed", Map.of("status", "OK", "jobs", 5234),
                "google", Map.of("status", "OK", "jobs", 3102),
                "zip_recruiter", Map.of("status", "OK", "jobs", 1890),
                "glassdoor", Map.of("status", "OK", "jobs", 634)
            ),
            "totalJobs", 29404,
            "errors", 0,
            "nextSweep", "2026-09-16T10:12:00Z"
        );
    }

    @PostMapping("/run")
    public Map<String, Object> runSweep() {
        return Map.of("status", "STARTED");
    }
}
