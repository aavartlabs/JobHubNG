package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;
import java.time.Instant;

@Entity
@Table(name = "jobs_raw", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class JobRaw {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "source_id", nullable = false)
    private Long sourceId;
    @Column(name = "external_job_id", length = 500)
    private String externalJobId;
    @Column(columnDefinition = "TEXT")
    private String payload;
    @Column(name = "payload_hash", nullable = false, length = 128)
    private String payloadHash;
    @Column(name = "fetched_at", nullable = false)
    private Instant fetchedAt;
    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default private Instant createdAt = Instant.now();
}
