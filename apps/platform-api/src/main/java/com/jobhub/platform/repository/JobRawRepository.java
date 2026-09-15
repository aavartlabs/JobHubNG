package com.jobhub.platform.repository;

import com.jobhub.platform.domain.JobRaw;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface JobRawRepository extends JpaRepository<JobRaw, Long> {
    Optional<JobRaw> findBySourceIdAndExternalJobIdAndPayloadHash(Long sourceId, String externalJobId, String payloadHash);
}
