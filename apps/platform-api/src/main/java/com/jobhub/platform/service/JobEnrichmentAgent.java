package com.jobhub.platform.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.jobhub.platform.config.OllamaConfig;
import com.jobhub.platform.domain.AiProcessingRun;
import com.jobhub.platform.repository.AiProcessingRunRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.time.Instant;
import java.util.*;

@Service
@RequiredArgsConstructor
@Slf4j
public class JobEnrichmentAgent {

    private final OllamaConfig ollamaConfig;
    private final RestTemplate restTemplate;
    private final AiProcessingRunRepository aiProcessingRunRepository;
    private final ObjectMapper objectMapper;

    @SuppressWarnings("unchecked")
    public Map<String, Object> enrichJob(Long jobRawId, String correlationId, String jobDescription) {
        log.info("Enriching job {} with correlation {}", jobRawId, correlationId);

        String systemPrompt = "You are a Job Enrichment Agent. Analyze job postings and extract structured metadata. " +
            "Return ONLY valid JSON with keys: country, city, employmentType, workMode, seniority, " +
            "experienceMin, experienceMax, skills (array of objects with name and importance), confidence (0-1).";

        String userPrompt = "Analyze this job posting and extract metadata:\n\n" + jobDescription;

        try {
            Map<String, Object> requestBody = new LinkedHashMap<>();
            requestBody.put("model", ollamaConfig.getModel());
            requestBody.put("prompt", systemPrompt + "\n\n" + userPrompt);
            requestBody.put("stream", false);
            requestBody.put("options", Map.of("temperature", 0.1, "num_predict", 512));

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            HttpEntity<Map<String, Object>> entity = new HttpEntity<>(requestBody, headers);

            String url = ollamaConfig.getBaseUrl() + "/api/generate";
            log.debug("Calling Ollama at {}", url);

            ResponseEntity<JsonNode> response = restTemplate.exchange(url, HttpMethod.POST, entity, JsonNode.class);

            JsonNode body = response.getBody();
            if (body == null || !body.has("response")) {
                throw new RuntimeException("Invalid response from Ollama: " + body);
            }

            String rawResponse = body.get("response").asText();

            // Clean up response - extract JSON if wrapped in markdown
            String json = rawResponse;
            if (json.contains("```json")) {
                json = json.substring(json.indexOf("```json") + 7);
                if (json.contains("```")) json = json.substring(0, json.indexOf("```"));
            } else if (json.contains("```")) {
                json = json.substring(json.indexOf("```") + 3);
                if (json.contains("```")) json = json.substring(0, json.indexOf("```"));
            }
            json = json.trim();

            // Parse JSON response
            Map<String, Object> result;
            try {
                result = objectMapper.readValue(json, Map.class);
            } catch (Exception e) {
                // If JSON parsing fails, wrap the raw response
                log.warn("Failed to parse enrichment JSON, wrapping raw response");
                result = Map.of("raw", rawResponse, "confidence", 0.1);
            }

            // Record the AI run
            AiProcessingRun run = AiProcessingRun.builder()
                .entityType("JOB_RAW")
                .entityId(jobRawId)
                .agentName("JobEnrichmentAgent")
                .agentVersion("1.0.0")
                .modelName(ollamaConfig.getModel())
                .promptVersion("v1")
                .outputJson(json)
                .confidence(result.containsKey("confidence") ? ((Number) result.get("confidence")).doubleValue() : 0.5)
                .status("SUCCESS")
                .traceId(UUID.randomUUID().toString())
                .startedAt(Instant.now().minusSeconds(10))
                .completedAt(Instant.now())
                .build();
            aiProcessingRunRepository.save(run);

            Map<String, Object> enrichment = new LinkedHashMap<>();
            enrichment.put("status", "SUCCESS");
            enrichment.put("jobRawId", jobRawId);
            enrichment.put("correlationId", correlationId);
            enrichment.put("enrichment", result);
            enrichment.put("agentRunId", run.getId());
            enrichment.put("traceId", run.getTraceId());

            return enrichment;

        } catch (Exception e) {
            log.error("Enrichment failed for job {}: {}", jobRawId, e.getMessage(), e);

            AiProcessingRun run = AiProcessingRun.builder()
                .entityType("JOB_RAW")
                .entityId(jobRawId)
                .agentName("JobEnrichmentAgent")
                .agentVersion("1.0.0")
                .modelName(ollamaConfig.getModel())
                .promptVersion("v1")
                .status("FAILED")
                .traceId(UUID.randomUUID().toString())
                .startedAt(Instant.now().minusSeconds(10))
                .completedAt(Instant.now())
                .errorCode("ENRICHMENT_ERROR")
                .errorMessage(e.getMessage())
                .build();
            aiProcessingRunRepository.save(run);

            return Map.of(
                "status", "FAILED",
                "jobRawId", jobRawId,
                "correlationId", correlationId,
                "error", e.getMessage(),
                "traceId", run.getTraceId()
            );
        }
    }
}
