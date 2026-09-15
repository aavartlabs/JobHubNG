package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;
import java.time.Instant;

@Entity
@Table(name = "jobs", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class Job {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "canonical_title", nullable = false, length = 500)
    private String canonicalTitle;
    @Column(name = "normalized_description", nullable = false, columnDefinition = "TEXT")
    private String normalizedDescription;
    @Column(name = "company_id")
    private Long companyId;
    @Column(nullable = false, length = 40)
    @Builder.Default private String status = "DRAFT";
    @Column(name = "country_code", length = 10)
    private String countryCode;
    @Column(length = 200)
    private String city;
    @Column(name = "published_at")
    private Instant publishedAt;
    @Column(name = "expires_at")
    private Instant expiresAt;
    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default private Instant createdAt = Instant.now();
    @Column(name = "updated_at", nullable = false)
    @Builder.Default private Instant updatedAt = Instant.now();
    @Version
    @Builder.Default private Long version = 0L;
}
