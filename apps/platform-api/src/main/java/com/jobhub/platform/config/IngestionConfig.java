package com.jobhub.platform.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Data
@Configuration
@ConfigurationProperties(prefix = "ingestion")
public class IngestionConfig {
    private EverJobs everJobs = new EverJobs();
    private List<Keyword> keywords;
    private Scheduler scheduler = new Scheduler();

    @Data
    public static class EverJobs {
        private String apiUrl = "http://localhost:3001";
        private String apiKey = "jobhub-ng-dev-key-2026";
        private int maxResults = 10;
        private int timeoutSeconds = 180;
        private int maxRequestsPerMinute = 30;
    }

    @Data
    public static class Scheduler {
        private boolean enabled = true;
        private String cron = "0 0 * * * *"; // Every hour
    }

    @Data
    public static class Keyword {
        private String term;
        private List<String> locations;
        private String frequency = "hourly"; // hourly, daily
    }
}
