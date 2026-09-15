package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;
import java.time.Instant;

@Entity
@Table(name = "users", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class User {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "tenant_id")
    private Tenant tenant;
    @Column(nullable = false, unique = true, length = 320)
    private String email;
    @Column(name = "display_name", nullable = false, length = 200)
    private String displayName;
    @Column(name = "password_hash", nullable = false, length = 255)
    private String passwordHash;
    @Column(nullable = false, length = 30)
    @Builder.Default private String status = "ACTIVE";
    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default private Instant createdAt = Instant.now();
    @Column(name = "updated_at", nullable = false)
    @Builder.Default private Instant updatedAt = Instant.now();
}
