package com.jobhub.platform.controller;

import com.jobhub.platform.domain.JobRaw;
import com.jobhub.platform.repository.JobRawRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

@RestController
@RequestMapping("/api/v1/jobs")
@RequiredArgsConstructor
public class JobSearchController {

    private final JobRawRepository jobRawRepository;

    @GetMapping("/search")
    public Map<String, Object> search(
            @RequestParam(required = false, defaultValue = "") String q,
            @RequestParam(required = false, defaultValue = "0") int page,
            @RequestParam(required = false, defaultValue = "20") int size,
            @RequestParam(required = false) String location,
            @RequestParam(required = false) String company,
            @RequestParam(required = false) String source) {

        Pageable pageable = PageRequest.of(page, Math.min(size, 50));
        Page<JobRaw> results;

        if (q != null && !q.isBlank()) {
            results = jobRawRepository.findByPayloadContainingIgnoreCase(q, pageable);
        } else {
            results = jobRawRepository.findAll(pageable);
        }

        List<Map<String, Object>> jobs = results.getContent().stream()
            .map(raw -> Map.<String, Object>of(
                "id", raw.getId(),
                "externalJobId", raw.getExternalJobId(),
                "sourceId", raw.getSourceId(),
                "fetchedAt", raw.getFetchedAt().toString()
            ))
            .collect(Collectors.toList());

        return Map.of(
            "jobs", jobs,
            "total", results.getTotalElements(),
            "page", page,
            "size", size,
            "totalPages", results.getTotalPages()
        );
    }

    @GetMapping("/{id}")
    public Map<String, Object> getJob(@PathVariable Long id) {
        return jobRawRepository.findById(id)
            .map(raw -> Map.<String, Object>of(
                "id", raw.getId(),
                "externalJobId", raw.getExternalJobId(),
                "payload", raw.getPayload(),
                "fetchedAt", raw.getFetchedAt().toString()
            ))
            .orElse(Map.of("error", "Job not found"));
    }
}
