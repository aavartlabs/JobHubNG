package com.jobhub.platform.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.jobhub.platform.domain.OutboxEvent;
import com.jobhub.platform.repository.OutboxEventRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class OutboxService {
    private final OutboxEventRepository repository;
    private final ObjectMapper objectMapper;

    @Transactional
    public void publish(String eventType, String aggregateType, String aggregateId,
                        Long tenantId, String correlationId, Object payload) {
        OutboxEvent event = OutboxEvent.builder()
            .id(UUID.randomUUID())
            .eventType(eventType)
            .aggregateType(aggregateType)
            .aggregateId(aggregateId)
            .tenantId(tenantId)
            .correlationId(correlationId)
            .payload(toJson(payload))
            .status("PENDING")
            .attempts(0)
            .createdAt(Instant.now())
            .build();
        repository.save(event);
    }

    @Scheduled(fixedDelayString = "${jobhub.outbox.fixed-delay-ms:2000}")
    @Transactional
    public void processPendingEvents() {
        List<OutboxEvent> pending = repository.findByStatusOrderByCreatedAtAsc("PENDING");
        for (OutboxEvent event : pending) {
            event.setStatus("PUBLISHED");
            event.setPublishedAt(Instant.now());
            repository.save(event);
        }
    }

    private String toJson(Object payload) {
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (Exception e) {
            return "{}";
        }
    }
}
