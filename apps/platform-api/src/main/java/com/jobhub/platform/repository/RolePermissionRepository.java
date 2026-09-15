package com.jobhub.platform.repository;

import com.jobhub.platform.domain.RolePermission;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.List;

public interface RolePermissionRepository extends JpaRepository<RolePermission, Long> {
    @Query("SELECT p.permissionKey FROM RolePermission rp JOIN Permission p ON rp.permission.id = p.id WHERE rp.role.id = :roleId")
    List<String> findPermissionKeysByRoleId(@Param("roleId") Long roleId);
}
