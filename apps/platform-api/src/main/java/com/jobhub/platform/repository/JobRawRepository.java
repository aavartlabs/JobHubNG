package com.jobhub.platform.repository;

import com.jobhub.platform.domain.JobRaw;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface JobRawRepository extends JpaRepository<JobRaw, Long> {
    List<JobRaw> findBySourceIdAndExternalJobId(Long sourceId, String externalJobId);
    boolean existsBySourceIdAndExternalJobId(Long sourceId, String externalJobId);
}
