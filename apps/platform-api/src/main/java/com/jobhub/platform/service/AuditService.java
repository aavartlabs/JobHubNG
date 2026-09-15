package com.jobhub.platform.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.jobhub.platform.domain.AuditEvent;
import com.jobhub.platform.repository.AuditEventRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class AuditService {
    private final AuditEventRepository repository;
    private final ObjectMapper objectMapper;

    public void recordLogin(Long actorId, Long tenantId, String email, String correlationId) {
        record("LOGIN", "USER", actorId, tenantId, correlationId, Map.of("email", email));
    }

    public void record(String eventType, String actorType, Long actorId, Long tenantId,
                       String correlationId, Object payload) {
        AuditEvent event = AuditEvent.builder()
            .eventType(eventType)
            .actorType(actorType)
            .actorId(actorId)
            .tenantId(tenantId)
            .correlationId(correlationId)
            .payload(toJson(payload))
            .createdAt(Instant.now())
            .build();
        repository.save(event);
    }

    private String toJson(Object payload) {
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (Exception e) {
            return "{}";
        }
    }
}
