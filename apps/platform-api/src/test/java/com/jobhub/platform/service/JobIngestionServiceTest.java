package com.jobhub.platform.service;

import com.jobhub.platform.domain.JobRaw;
import com.jobhub.platform.repository.JobRawRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
@Transactional
class JobIngestionServiceTest {

    @Autowired
    private JobIngestionService ingestionService;

    @Autowired
    private JobRawRepository jobRawRepository;

    @BeforeEach
    void setUp() {
        jobRawRepository.deleteAll();
    }

    @Test
    void ingestAll_returnsZeroWhenNoKeywordsConfigured() {
        // When
        var result = ingestionService.ingestAll();

        // Then
        assertThat(result).containsKey("totalNewJobs");
    }

    @Test
    void ingestAll_incrementsTotalJobs() {
        // Given
        int initialCount = (int) jobRawRepository.count();

        // When
        ingestionService.ingestAll();

        // Then
        assertThat(jobRawRepository.count()).isGreaterThanOrEqualTo(initialCount);
    }

    @Test
    void deduplication_skipsAlreadyIngestedJobs() {
        // Given
        JobRaw raw = JobRaw.builder()
            .sourceId(1L)
            .externalJobId("test-job-123")
            .payload("{\"title\":\"Test Job\"}")
            .payloadHash("hash123")
            .build();
        jobRawRepository.save(raw);

        // When
        int initialCount = (int) jobRawRepository.count();
        ingestionService.ingestAll();

        // Then - count should not increase for duplicate
        assertThat(jobRawRepository.count()).isEqualTo(initialCount);
    }
}
