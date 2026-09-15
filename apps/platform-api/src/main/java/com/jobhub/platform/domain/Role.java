package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "roles", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class Role {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "role_key", nullable = false, unique = true, length = 80)
    private String roleKey;
    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;
}
