package com.jobhub.platform.controller;

import com.jobhub.platform.service.JobIngestionService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/admin/ingestion")
@RequiredArgsConstructor
public class IngestionController {

    private final JobIngestionService ingestionService;

    @PostMapping("/run")
    public Map<String, Object> runIngestion() {
        // Run async - don't block the HTTP thread
        new Thread(() -> {
            try {
                ingestionService.ingestAll();
            } catch (Exception e) {
                // Log error
            }
        }).start();
        return Map.of("status", "STARTED", "message", "Ingestion started in background");
    }

    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of("status", "READY", "service", "job-ingestion");
    }
}
