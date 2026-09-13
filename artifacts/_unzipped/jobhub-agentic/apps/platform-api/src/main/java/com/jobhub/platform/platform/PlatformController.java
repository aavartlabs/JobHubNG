package com.jobhub.platform.platform;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/v1")
public class PlatformController {
    private final JdbcTemplate jdbc;
    public PlatformController(JdbcTemplate jdbc) { this.jdbc=jdbc; }

    @GetMapping("/public/status")
    public Map<String,Object> publicStatus() { return Map.of("platform","JobHub","phase","0+1","status","READY"); }

    @GetMapping("/platform/me")
    public Map<String,Object> platformMe() { return Map.of("message","Authenticated JobHub platform shell"); }

    @PreAuthorize("hasRole('ADMIN')")
    @GetMapping("/admin/dataflow")
    public Map<String,Object> dataflow() {
        return Map.of(
          "users", jdbc.queryForObject("SELECT count(*) FROM users", Long.class),
          "roles", jdbc.queryForObject("SELECT count(*) FROM roles", Long.class),
          "auditEvents", jdbc.queryForObject("SELECT count(*) FROM audit_events", Long.class),
          "outboxPending", jdbc.queryForObject("SELECT count(*) FROM outbox_events WHERE status='PENDING'", Long.class),
          "outboxPublished", jdbc.queryForObject("SELECT count(*) FROM outbox_events WHERE status='PUBLISHED'", Long.class)
        );
    }
}
