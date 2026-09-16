package com.jobhub.platform.repository;

import com.jobhub.platform.domain.JobRequisition;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface JobRequisitionRepository extends JpaRepository<JobRequisition, Long> {
    
    @Query("SELECT j FROM JobRequisition j WHERE " +
           "LOWER(j.title) LIKE LOWER(CONCAT('%', :query, '%')) OR " +
           "LOWER(j.department) LIKE LOWER(CONCAT('%', :query, '%')) OR " +
           "LOWER(j.description) LIKE LOWER(CONCAT('%', :query, '%'))")
    Page<JobRequisition> search(@Param("query") String query, Pageable pageable);
    
    Page<JobRequisition> findByStatus(String status, Pageable pageable);
    
    Page<JobRequisition> findByCreatedBy(Long createdBy, Pageable pageable);
}
