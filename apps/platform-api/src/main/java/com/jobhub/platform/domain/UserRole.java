package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "user_roles", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor
public class UserRole {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    private User user;
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "role_id", nullable = false)
    private Role role;
}
