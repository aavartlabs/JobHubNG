package com.jobhub.platform.controller;

import com.jobhub.platform.service.OutboxService;
import com.jobhub.platform.domain.JobRaw;
import com.jobhub.platform.repository.JobRawRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/internal/v1")
@RequiredArgsConstructor
public class JobController {

    private final JobRawRepository jobRawRepository;
    private final OutboxService outboxService;

    @PostMapping("/ingestion/jobs")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Map<String, Object>> ingestJob(@RequestBody Map<String, Object> payload) {
        String correlationId = UUID.randomUUID().toString();

        JobRaw raw = JobRaw.builder()
            .sourceId(1L)
            .externalJobId((String) payload.get("externalId"))
            .payload(payload.toString())
            .payloadHash(UUID.randomUUID().toString().substring(0, 32))
            .fetchedAt(Instant.now())
            .build();
        jobRawRepository.save(raw);

        outboxService.publish("JOB_RECEIVED", "JOB_RAW", raw.getId().toString(),
            null, correlationId, Map.of("jobRawId", raw.getId()));

        return ResponseEntity.accepted().body(Map.of(
            "jobRawId", raw.getId(),
            "correlationId", correlationId,
            "status", "RECEIVED"
        ));
    }
}
