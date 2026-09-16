package com.jobhub.platform.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.jobhub.platform.config.IngestionConfig;
import com.jobhub.platform.domain.JobRaw;
import com.jobhub.platform.repository.JobRawRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.*;

@Service
@RequiredArgsConstructor
@Slf4j
public class JobIngestionService {

    private final EverJobsClient everJobsClient;
    private final JobRawRepository jobRawRepository;
    private final OutboxService outboxService;
    private final IngestionConfig config;

    @Transactional
    public int ingestKeyword(IngestionConfig.Keyword keyword) {
        int newJobs = 0;
        List<JsonNode> jobs = everJobsClient.search(keyword.getTerm(), config.getEverJobs().getMaxResults());

        for (JsonNode job : jobs) {
            String externalJobId = extractField(job, "id", "");
            String sourceSite = extractField(job, "site", "everjobs");
            String payload = job.toString();
            String payloadHash = sha256(payload);

            // Idempotency check - skip if we already have this job
            if (jobRawRepository.existsBySourceIdAndExternalJobId(1L, externalJobId)) {
                continue;
            }

            // Store raw job
            JobRaw raw = JobRaw.builder()
                .sourceId(1L)
                .externalJobId(externalJobId)
                .payload(payload)
                .payloadHash(payloadHash)
                .fetchedAt(Instant.now())
                .build();
            jobRawRepository.save(raw);

            // Publish outbox event
            String correlationId = UUID.randomUUID().toString();
            outboxService.publish("JOB_RECEIVED", "JOB_RAW", raw.getId().toString(),
                null, correlationId, Map.of(
                    "jobRawId", raw.getId(),
                    "keyword", keyword.getTerm(),
                    "title", extractField(job, "title", ""),
                    "company", extractField(job, "companyName", ""),
                    "site", sourceSite
                ));

            newJobs++;
        }

        log.info("Ingested {} new jobs for keyword: {}", newJobs, keyword.getTerm());
        return newJobs;
    }

    public Map<String, Object> ingestAll() {
        Map<String, Object> result = new LinkedHashMap<>();
        int total = 0;

        if (config.getKeywords() != null) {
            for (IngestionConfig.Keyword keyword : config.getKeywords()) {
                try {
                    int count = ingestKeyword(keyword);
                    total += count;
                    result.put(keyword.getTerm(), count);
                } catch (Exception e) {
                    result.put(keyword.getTerm(), "ERROR: " + e.getMessage());
                    log.error("Failed to ingest keyword: {}", keyword.getTerm(), e);
                }
            }
        }

        result.put("totalNewJobs", total);
        return result;
    }

    private String extractField(JsonNode node, String field, String defaultValue) {
        return node.has(field) && !node.get(field).isNull() ? node.get(field).asText() : defaultValue;
    }

    private String sha256(String input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(input.getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder().encodeToString(hash);
        } catch (NoSuchAlgorithmException e) {
            return UUID.randomUUID().toString();
        }
    }
}
