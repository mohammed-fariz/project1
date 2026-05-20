-- ==========================================
-- CREATE DATABASE
-- ==========================================
CREATE DATABASE IF NOT EXISTS site_engineer_ai;

USE site_engineer_ai;

-- ==========================================
-- PROJECTS TABLE
-- ==========================================
CREATE TABLE projects (

    id INT PRIMARY KEY AUTO_INCREMENT,

    project_name VARCHAR(255),

    airflow_unit VARCHAR(50),

    duct_size_unit VARCHAR(50)

);

-- ==========================================
-- ROOMS TABLE
-- ==========================================
CREATE TABLE rooms (

    id INT PRIMARY KEY AUTO_INCREMENT,

    project_id INT,

    room_name VARCHAR(255),

    grille_size VARCHAR(50),

    airflow INT,

    duct_diameter INT,

    return_type VARCHAR(255),

    FOREIGN KEY (project_id)
    REFERENCES projects(id)

);

-- ==========================================
-- DUCT NETWORK TABLE
-- ==========================================
CREATE TABLE duct_network (

    id INT PRIMARY KEY AUTO_INCREMENT,

    project_id INT,

    network_type VARCHAR(50),

    section_name VARCHAR(255),

    duct_size VARCHAR(50),

    branch_to VARCHAR(255),

    branch_diameter INT,

    FOREIGN KEY (project_id)
    REFERENCES projects(id)

);

-- ==========================================
-- SPECIAL ELEMENTS TABLE
-- ==========================================
CREATE TABLE special_elements (

    id INT PRIMARY KEY AUTO_INCREMENT,

    project_id INT,

    element_type VARCHAR(255),

    description TEXT,

    location_info TEXT,

    FOREIGN KEY (project_id)
    REFERENCES projects(id)

);

-- ==========================================
-- CHAT HISTORY TABLE
-- ==========================================
CREATE TABLE chat_history (

    id INT PRIMARY KEY AUTO_INCREMENT,

    session_id VARCHAR(255),

    role VARCHAR(50),

    message TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

);

-- ==========================================
-- INSERT PROJECT
-- ==========================================
INSERT INTO projects (

    project_name,
    airflow_unit,
    duct_size_unit

)

VALUES (

    'Residential HVAC Layout',
    'CFM',
    'inches'

);

-- ==========================================
-- INSERT ROOM DATA
-- ==========================================
INSERT INTO rooms (

    project_id,
    room_name,
    grille_size,
    airflow,
    duct_diameter,
    return_type

)

VALUES

(1, 'Bedroom 1', '4x10', 78, 6, NULL),

(1, 'Bedroom 1', '4x10', 78, 6, NULL),

(1, 'Bedroom 2', '4x10', 76, 6, NULL),

(1, 'Bedroom 3', '4x14', 79, 6, NULL),

(1, 'Living Area', '4x10', 47, 6, NULL),

(1, 'Other Area', '2x10', 39, 6, NULL);

-- ==========================================
-- INSERT MAIN TRUNK DATA
-- ==========================================
INSERT INTO duct_network (

    project_id,
    network_type,
    section_name,
    duct_size,
    branch_to,
    branch_diameter

)

VALUES

(1, 'main_trunk', 'Bedroom1 to Core', '10x6', NULL, NULL),

(1, 'main_trunk', 'Core to Bedroom2', '12x6', NULL, NULL),

(1, 'main_trunk', 'Bedroom2 branch', '16x6', NULL, NULL);

-- ==========================================
-- INSERT BRANCH DATA
-- ==========================================
INSERT INTO duct_network (

    project_id,
    network_type,
    section_name,
    duct_size,
    branch_to,
    branch_diameter

)

VALUES

(1, 'branch', NULL, NULL, 'Bedroom 1', 6),

(1, 'branch', NULL, NULL, 'Bedroom 2', 6),

(1, 'branch', NULL, NULL, 'Bedroom 3', 6),

(1, 'branch', NULL, NULL, 'Living Area', 6);

-- ==========================================
-- INSERT SPECIAL ELEMENTS
-- ==========================================
INSERT INTO special_elements (

    project_id,
    element_type,
    description,
    location_info

)

VALUES

(
    1,
    'Linen',
    NULL,
    'Central Right'
),

(
    1,
    'S&P',
    'Supply & Return/Plenum areas',
    'Left bottom, Right side'
),

(
    1,
    'S & BDL P',
    NULL,
    'Left side utility'
);