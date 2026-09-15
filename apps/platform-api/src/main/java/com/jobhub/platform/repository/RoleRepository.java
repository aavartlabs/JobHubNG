package com.jobhub.platform.repository;

import com.jobhub.platform.domain.Role;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface RoleRepository extends JpaRepository<Role, Long> {
    Optional<Role> findByRoleKey(String roleKey);
}
