package com.jobhub.platform.common;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.UUID;

@Component
public class OutboxPublisher {
    private final JdbcTemplate jdbc;
    public OutboxPublisher(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    @Scheduled(fixedDelayString = "${jobhub.outbox.fixed-delay-ms:2000}")
    public void publishPending() {
        List<UUID> ids = jdbc.query("""
          SELECT id FROM outbox_events WHERE status='PENDING' ORDER BY created_at LIMIT 25
        """, (rs,i)->rs.getObject(1, UUID.class));
        for (UUID id : ids) {
            jdbc.update("UPDATE outbox_events SET status='PUBLISHED',published_at=now(),attempts=attempts+1 WHERE id=? AND status='PENDING'", id);
        }
    }
}
