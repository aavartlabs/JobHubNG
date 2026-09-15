package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "outbox_events", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class OutboxEvent {
    @Id
    @Builder.Default private UUID id = UUID.randomUUID();
    @Column(name = "event_type", nullable = false, length = 120)
    private String eventType;
    @Column(name = "aggregate_type", nullable = false, length = 80)
    private String aggregateType;
    @Column(name = "aggregate_id", nullable = false, length = 120)
    private String aggregateId;
    @Column(name = "tenant_id")
    private Long tenantId;
    @Column(name = "correlation_id", nullable = false, length = 120)
    private String correlationId;
    @Column(columnDefinition = "JSONB", nullable = false)
    private String payload;
    @Column(nullable = false, length = 30)
    @Builder.Default private String status = "PENDING";
    @Column(nullable = false)
    @Builder.Default private Integer attempts = 0;
    @Column(name = "next_attempt_at")
    private Instant nextAttemptAt;
    @Column(name = "published_at")
    private Instant publishedAt;
    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default private Instant createdAt = Instant.now();
}
