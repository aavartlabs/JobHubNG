package com.jobhub.platform.repository;

import com.jobhub.platform.domain.Candidate;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.Optional;

public interface CandidateRepository extends JpaRepository<Candidate, Long> {
    Optional<Candidate> findByEmail(String email);
    
    @Query("SELECT c FROM Candidate c WHERE " +
           "LOWER(c.fullName) LIKE LOWER(CONCAT('%', :query, '%')) OR " +
           "LOWER(c.skills) LIKE LOWER(CONCAT('%', :query, '%')) OR " +
           "LOWER(c.currentCompany) LIKE LOWER(CONCAT('%', :query, '%')) OR " +
           "LOWER(c.currentTitle) LIKE LOWER(CONCAT('%', :query, '%'))")
    Page<Candidate> search(@Param("query") String query, Pageable pageable);
    
    Page<Candidate> findByStatus(String status, Pageable pageable);
}
