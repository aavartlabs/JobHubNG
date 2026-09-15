package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "permissions", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class Permission {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "permission_key", nullable = false, unique = true, length = 120)
    private String permissionKey;
    @Column(nullable = false, length = 250)
    private String description;
}
