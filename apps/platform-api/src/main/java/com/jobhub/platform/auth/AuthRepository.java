package com.jobhub.platform.auth;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.List;
import java.util.Map;

@Repository
public class AuthRepository {
    private final JdbcTemplate jdbc;
    public AuthRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public Map<String,Object> findUserByEmail(String email) {
        return jdbc.queryForMap("""
          SELECT u.id,u.email,u.display_name,u.password_hash,u.status,
                 COALESCE(t.tenant_key,'PLATFORM') tenant_key
          FROM users u LEFT JOIN tenants t ON t.id=u.tenant_id
          WHERE lower(u.email)=lower(?)
        """, email);
    }

    public List<String> findRoles(long userId) {
        return jdbc.query("SELECT r.role_key FROM roles r JOIN user_roles ur ON ur.role_id=r.id WHERE ur.user_id=? ORDER BY r.role_key",
          (rs,i)->rs.getString(1), userId);
    }

    public List<String> findPermissions(long userId) {
        return jdbc.query("""
          SELECT DISTINCT p.permission_key
          FROM permissions p
          JOIN role_permissions rp ON rp.permission_id=p.id
          JOIN user_roles ur ON ur.role_id=rp.role_id
          WHERE ur.user_id=? ORDER BY p.permission_key
        """, (rs,i)->rs.getString(1), userId);
    }

    public long ensureDemoUser(String email, String displayName, String passwordHash, String roleKey, long tenantId) {
        jdbc.update("""
          INSERT INTO users(tenant_id,email,display_name,password_hash) VALUES(?,?,?,?)
          ON CONFLICT(email) DO NOTHING
        """, tenantId, email, displayName, passwordHash);
        Map<String,Object> user = jdbc.queryForMap("SELECT id FROM users WHERE email=?", email);
        long userId = ((Number)user.get("id")).longValue();
        jdbc.update("""
          INSERT INTO user_roles(user_id,role_id)
          SELECT ?,id FROM roles WHERE role_key=?
          ON CONFLICT DO NOTHING
        """, userId, roleKey);
        return userId;
    }
}
