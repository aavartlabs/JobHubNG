package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;
import java.time.Instant;

@Entity
@Table(name = "candidates", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class Candidate {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false, length = 320)
    private String email;
    @Column(name = "full_name", nullable = false, length = 200)
    private String fullName;
    @Column(length = 20)
    private String phone;
    @Column(name = "linkedin_url", length = 500)
    private String linkedinUrl;
    @Column(name = "resume_url", length = 500)
    private String resumeUrl;
    @Column(columnDefinition = "TEXT")
    private String skills;
    @Column(columnDefinition = "TEXT")
    private String experience;
    @Column(length = 200)
    private String currentTitle;
    @Column(length = 200)
    private String currentCompany;
    @Column(length = 50)
    private String location;
    @Column(nullable = false, length = 30)
    @Builder.Default private String status = "ACTIVE";
    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default private Instant createdAt = Instant.now();
}
