package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;
import java.time.Instant;

@Entity
@Table(name = "ai_processing_runs", schema = "jobhub_ai")
@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class AiProcessingRun {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "entity_type", nullable = false, length = 50)
    private String entityType;
    @Column(name = "entity_id", nullable = false)
    private Long entityId;
    @Column(name = "workflow_instance_id", length = 100)
    private String workflowInstanceId;
    @Column(name = "agent_name", nullable = false, length = 200)
    private String agentName;
    @Column(name = "agent_version", nullable = false, length = 50)
    private String agentVersion;
    @Column(name = "model_name", length = 100)
    private String modelName;
    @Column(name = "prompt_version", length = 100)
    private String promptVersion;
    @Column(name = "input_hash", length = 128)
    private String inputHash;
    @Column(columnDefinition = "JSONB")
    private String outputJson;
    @Column(precision = 5, scale = 4)
    private Double confidence;
    @Column(nullable = false, length = 30)
    @Builder.Default private String status = "PENDING";
    @Column(name = "trace_id", length = 100)
    private String traceId;
    @Column(name = "started_at")
    private Instant startedAt;
    @Column(name = "completed_at")
    private Instant completedAt;
    @Column(name = "error_code", length = 100)
    private String errorCode;
    @Column(name = "error_message", columnDefinition = "TEXT")
    private String errorMessage;
}
