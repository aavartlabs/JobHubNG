package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;
import java.time.Instant;

@Entity
@Table(name = "audit_events", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class AuditEvent {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "event_type", nullable = false, length = 120)
    private String eventType;
    @Column(name = "actor_type", nullable = false, length = 40)
    private String actorType;
    @Column(name = "actor_id")
    private Long actorId;
    @Column(name = "tenant_id")
    private Long tenantId;
    @Column(name = "correlation_id", nullable = false, length = 120)
    private String correlationId;
    @Column(columnDefinition = "JSONB", nullable = false)
    private String payload;
    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default private Instant createdAt = Instant.now();
}
