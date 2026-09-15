package com.jobhub.platform.common;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.Map;
import java.util.UUID;

@Service
public class AuditOutboxService {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public AuditOutboxService(JdbcTemplate jdbc, ObjectMapper mapper) {
        this.jdbc = jdbc; this.mapper = mapper;
    }

    @Transactional
    public void recordLogin(long userId, long tenantId, String email, String correlationId) {
        String payload = JsonSupport.write(mapper, Map.of("email", email, "timestamp", OffsetDateTime.now().toString()));
        jdbc.update("""
          INSERT INTO audit_events(event_type,actor_type,actor_id,tenant_id,correlation_id,payload)
          VALUES('USER_LOGIN','USER',?,?,?,?::jsonb)
        """, userId, tenantId, correlationId, payload);
        jdbc.update("""
          INSERT INTO outbox_events(id,event_type,aggregate_type,aggregate_id,tenant_id,correlation_id,payload)
          VALUES(?,?,?,?,?,?,?::jsonb)
        """, UUID.randomUUID(), "USER_LOGIN", "USER", String.valueOf(userId), tenantId, correlationId, payload);
    }
}
