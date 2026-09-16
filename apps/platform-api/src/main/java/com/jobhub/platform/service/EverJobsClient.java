package com.jobhub.platform.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.jobhub.platform.config.IngestionConfig;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.*;

@Service
@RequiredArgsConstructor
@Slf4j
public class EverJobsClient {

    private final IngestionConfig config;
    private final RestTemplate restTemplate;
    private final ObjectMapper objectMapper;

    public List<JsonNode> search(String query, int maxResults) {
        String url = config.getEverJobs().getApiUrl() + "/api/jobs/search";

        Map<String, Object> request = Map.of(
            "input", Map.of(
                "query", query,
                "results", Math.min(maxResults, config.getEverJobs().getMaxResults())
            )
        );

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("x-api-key", config.getEverJobs().getApiKey());
        HttpEntity<Map<String, Object>> entity = new HttpEntity<>(request, headers);

        try {
            ResponseEntity<JsonNode> response = restTemplate.exchange(
                url, HttpMethod.POST, entity, JsonNode.class);

            JsonNode body = response.getBody();
            if (body == null || !body.has("jobs")) {
                log.warn("Invalid EverJobs response for query: {}", query);
                return List.of();
            }

            List<JsonNode> jobs = new ArrayList<>();
            body.get("jobs").forEach(jobs::add);
            log.info("EverJobs returned {} jobs for query: {}", jobs.size(), query);
            return jobs;

        } catch (Exception e) {
            log.error("EverJobs search failed for query {}: {}", query, e.getMessage());
            return List.of();
        }
    }
}
