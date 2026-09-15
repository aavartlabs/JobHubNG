package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;
import java.time.Instant;

@Entity
@Table(name = "tenants", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class Tenant {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "tenant_key", nullable = false, unique = true, length = 80)
    private String tenantKey;
    @Column(nullable = false, length = 200)
    private String name;
    @Column(nullable = false, length = 30)
    @Builder.Default private String status = "ACTIVE";
    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default private Instant createdAt = Instant.now();
}
