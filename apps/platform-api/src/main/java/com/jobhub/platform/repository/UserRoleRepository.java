package com.jobhub.platform.repository;

import com.jobhub.platform.domain.UserRole;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.List;

public interface UserRoleRepository extends JpaRepository<UserRole, Long> {
    @Query("SELECT r.roleKey FROM UserRole ur JOIN Role r ON ur.role.id = r.id WHERE ur.user.id = :userId")
    List<String> findRoleKeysByUserId(@Param("userId") Long userId);
}
