package com.jobhub.platform.repository;

import com.jobhub.platform.domain.JobRaw;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface JobRawRepository extends JpaRepository<JobRaw, Long> {
    List<JobRaw> findBySourceIdAndExternalJobId(Long sourceId, String externalJobId);
    boolean existsBySourceIdAndExternalJobId(Long sourceId, String externalJobId);
    
    @Query("SELECT j FROM JobRaw j WHERE LOWER(j.payload) LIKE LOWER(CONCAT('%', :query, '%'))")
    Page<JobRaw> findByPayloadContainingIgnoreCase(@Param("query") String query, Pageable pageable);
}
