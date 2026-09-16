package com.jobhub.platform.service;

import com.jobhub.platform.config.IngestionConfig;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.Map;

@Component
@RequiredArgsConstructor
@Slf4j
public class IngestionScheduler {

    private final JobIngestionService ingestionService;
    private final IngestionConfig config;

    @Scheduled(cron = "${ingestion.scheduler.cron:0 0 * * * *}")
    public void scheduledIngestion() {
        if (!config.getScheduler().isEnabled()) {
            log.debug("Ingestion scheduler disabled, skipping.");
            return;
        }

        log.info("Starting scheduled job ingestion...");
        long start = System.currentTimeMillis();

        try {
            Map<String, Object> result = ingestionService.ingestAll();
            long elapsed = System.currentTimeMillis() - start;
            log.info("Ingestion complete in {}ms: {}", elapsed, result);
        } catch (Exception e) {
            log.error("Scheduled ingestion failed", e);
        }
    }
}
