package com.jobhub.platform.domain;

import jakarta.persistence.*;
import lombok.*;
import java.time.Instant;

@Entity
@Table(name = "job_requisitions", schema = "jobhub")
@Data @NoArgsConstructor @AllArgsConstructor @Builder
public class JobRequisition {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false, length = 300)
    private String title;
    @Column(columnDefinition = "TEXT")
    private String description;
    @Column(length = 200)
    private String department;
    @Column(length = 200)
    private String location;
    @Column(length = 50)
    private String employmentType;
    @Column(length = 500)
    private String requiredSkills;
    @Column(length = 500)
    private String preferredSkills;
    @Column(precision = 10, scale = 2)
    private Double salaryMin;
    @Column(precision = 10, scale = 2)
    private Double salaryMax;
    @Column(length = 30)
    @Builder.Default private String status = "OPEN";
    @Column(name = "hiring_manager", length = 200)
    private String hiringManager;
    @Column(name = "created_by")
    private Long createdBy;
    @Column(name = "created_at", nullable = false, updatable = false)
    @Builder.Default private Instant createdAt = Instant.now();
    @Column(name = "updated_at", nullable = false)
    @Builder.Default private Instant updatedAt = Instant.now();
}
