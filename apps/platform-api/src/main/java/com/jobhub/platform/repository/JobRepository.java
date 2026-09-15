package com.jobhub.platform.repository;

import com.jobhub.platform.domain.Job;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface JobRepository extends JpaRepository<Job, Long> {
    List<Job> findByStatusOrderByPublishedAtDesc(String status);
}
