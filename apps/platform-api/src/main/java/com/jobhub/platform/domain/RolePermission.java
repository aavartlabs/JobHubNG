package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "role_permissions", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor
public class RolePermission {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "role_id", nullable = false)
    private Role role;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "permission_id", nullable = false)
    private Permission permission;
}
