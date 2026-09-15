package com.jobhub.platform.repository;

import com.jobhub.platform.domain.AiProcessingRun;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface AiProcessingRunRepository extends JpaRepository<AiProcessingRun, Long> {
    Optional<AiProcessingRun> findByEntityTypeAndEntityIdAndStatus(String entityType, Long entityId, String status);
}
