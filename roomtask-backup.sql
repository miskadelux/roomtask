-- MySQL dump 10.13  Distrib 8.4.13, for Linux (x86_64)
--
-- Host: localhost    Database: roomtask
-- ------------------------------------------------------
-- Server version	8.4.13

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `attachments`
--

DROP TABLE IF EXISTS `attachments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `attachments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticket_id` int NOT NULL,
  `report_id` int DEFAULT NULL,
  `stored_name` varchar(255) NOT NULL,
  `original_name` varchar(255) NOT NULL,
  `content_type` varchar(100) NOT NULL,
  `size` int NOT NULL,
  `uploaded_by` varchar(100) NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `stored_name` (`stored_name`),
  KEY `report_id` (`report_id`),
  KEY `ix_attachments_ticket_id` (`ticket_id`),
  CONSTRAINT `attachments_ibfk_1` FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`id`),
  CONSTRAINT `attachments_ibfk_2` FOREIGN KEY (`report_id`) REFERENCES `reports` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `attachments`
--

LOCK TABLES `attachments` WRITE;
/*!40000 ALTER TABLE `attachments` DISABLE KEYS */;
INSERT INTO `attachments` VALUES (1,8,8,'4a241de4ba2a4a3487cb2be185d04f8f.jpg','skiss över övningsområdet.jpg','image/jpeg',2663629,'public reporter','2026-11-13 22:14:51');
/*!40000 ALTER TABLE `attachments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `duplicate_matches`
--

DROP TABLE IF EXISTS `duplicate_matches`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `duplicate_matches` (
  `id` int NOT NULL AUTO_INCREMENT,
  `report_id` int NOT NULL,
  `candidate_ticket_id` int NOT NULL,
  `score` int NOT NULL,
  `decision` varchar(20) NOT NULL,
  `decided_by` int DEFAULT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `candidate_ticket_id` (`candidate_ticket_id`),
  KEY `decided_by` (`decided_by`),
  KEY `ix_duplicate_matches_report_id` (`report_id`),
  CONSTRAINT `duplicate_matches_ibfk_1` FOREIGN KEY (`report_id`) REFERENCES `reports` (`id`),
  CONSTRAINT `duplicate_matches_ibfk_2` FOREIGN KEY (`candidate_ticket_id`) REFERENCES `tickets` (`id`),
  CONSTRAINT `duplicate_matches_ibfk_3` FOREIGN KEY (`decided_by`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=12 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `duplicate_matches`
--

LOCK TABLES `duplicate_matches` WRITE;
/*!40000 ALTER TABLE `duplicate_matches` DISABLE KEYS */;
INSERT INTO `duplicate_matches` VALUES (11,7,6,86,'linked',1,'2026-11-12 22:59:47');
/*!40000 ALTER TABLE `duplicate_matches` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `reports`
--

DROP TABLE IF EXISTS `reports`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `reports` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticket_id` int NOT NULL,
  `source` varchar(20) NOT NULL,
  `reporter_discord_id` varchar(40) DEFAULT NULL,
  `reporter_label` varchar(100) DEFAULT NULL,
  `original_description` text NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `ix_reports_ticket_id` (`ticket_id`),
  CONSTRAINT `reports_ibfk_1` FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `reports`
--

LOCK TABLES `reports` WRITE;
/*!40000 ALTER TABLE `reports` DISABLE KEYS */;
INSERT INTO `reports` VALUES (6,6,'web',NULL,NULL,'lampan som hänger i taket är trasig behöver bytas','2026-11-12 22:59:28'),(7,6,'web',NULL,NULL,'det är en trasig lamap i taket','2026-11-12 22:59:47'),(8,8,'web',NULL,NULL,'printern ger mig vara spagetti','2026-11-13 22:14:51');
/*!40000 ALTER TABLE `reports` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `rooms`
--

DROP TABLE IF EXISTS `rooms`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `rooms` (
  `id` int NOT NULL AUTO_INCREMENT,
  `name` varchar(120) NOT NULL,
  `qr_token` varchar(64) NOT NULL,
  `active` tinyint(1) NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `name` (`name`),
  UNIQUE KEY `ix_rooms_qr_token` (`qr_token`)
) ENGINE=InnoDB AUTO_INCREMENT=7 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `rooms`
--

LOCK TABLES `rooms` WRITE;
/*!40000 ALTER TABLE `rooms` DISABLE KEYS */;
INSERT INTO `rooms` VALUES (1,'3D-printer rummet','2ebeuNSnQThZiTMud-pBSEPCstVdLKcy',1),(2,'Simulator rummet','Libdmr2Py513-hXduTxdEQBkTkYCqoXN',1),(3,'Dator rummet','FZ3WXyFUsoVvvHvMRjfXMcWqkpTYWfU2',1),(4,'Projektor rummet','0K2NhpCqBgYmqnmhjrK2XE1l0DCD_2ps',1),(5,'Mötes rummet','XwRpwNXZXurys88PwUVYYQrFKmeBdAiO',1),(6,'Vardagsrummet','wwpTvCPjDXcZB-O9BTZupZsXOGbbQF6L',1);
/*!40000 ALTER TABLE `rooms` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `ticket_comments`
--

DROP TABLE IF EXISTS `ticket_comments`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_comments` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticket_id` int NOT NULL,
  `user_id` int NOT NULL,
  `body` text NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `user_id` (`user_id`),
  KEY `ix_ticket_comments_ticket_id` (`ticket_id`),
  CONSTRAINT `ticket_comments_ibfk_1` FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`id`),
  CONSTRAINT `ticket_comments_ibfk_2` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `ticket_comments`
--

LOCK TABLES `ticket_comments` WRITE;
/*!40000 ALTER TABLE `ticket_comments` DISABLE KEYS */;
INSERT INTO `ticket_comments` VALUES (1,8,1,'jag har testat att skriva nya saker med printern','2026-11-14 22:01:03');
/*!40000 ALTER TABLE `ticket_comments` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `ticket_history`
--

DROP TABLE IF EXISTS `ticket_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ticket_history` (
  `id` int NOT NULL AUTO_INCREMENT,
  `ticket_id` int NOT NULL,
  `actor_user_id` int DEFAULT NULL,
  `actor_label` varchar(100) NOT NULL,
  `action` varchar(80) NOT NULL,
  `details` text,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  KEY `actor_user_id` (`actor_user_id`),
  KEY `ix_ticket_history_ticket_id` (`ticket_id`),
  CONSTRAINT `ticket_history_ibfk_1` FOREIGN KEY (`ticket_id`) REFERENCES `tickets` (`id`),
  CONSTRAINT `ticket_history_ibfk_2` FOREIGN KEY (`actor_user_id`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=52 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `ticket_history`
--

LOCK TABLES `ticket_history` WRITE;
/*!40000 ALTER TABLE `ticket_history` DISABLE KEYS */;
INSERT INTO `ticket_history` VALUES (38,6,NULL,'system','report_created','source=web; report_id=6','2026-11-12 22:59:28'),(39,6,NULL,'system','report_created','source=web; report_id=7','2026-11-12 22:59:47'),(40,6,NULL,'system','possible_duplicate_detected','ticket=6,score=85.5','2026-11-12 22:59:47'),(41,6,1,'admin','tickets_merged','source_ticket_id=7; match_id=11','2026-11-12 23:01:13'),(42,8,NULL,'system','report_created','source=web; report_id=8','2026-11-13 22:14:51'),(43,8,2,'labrat_1','claimed',NULL,'2026-11-13 22:25:06'),(44,8,2,'labrat_1','completed',NULL,'2026-11-13 22:25:08'),(45,8,2,'labrat_1','reopened_after_admin_discussion',NULL,'2026-11-13 22:25:11'),(46,8,2,'labrat_1','completed','Åtgärd utförd: jag har rensat al filament som har kronglat','2026-11-14 09:23:47'),(47,6,2,'labrat_1','claimed',NULL,'2026-11-14 20:54:38'),(48,6,2,'labrat_1','completed','Åtgärd utförd: jag har bytt lampan','2026-11-14 20:55:25'),(49,8,2,'labrat_1','reopened_after_admin_discussion','Ärendet återöppnades för fortsatt arbete.','2026-11-14 21:42:04'),(50,6,2,'labrat_1','reopened_after_admin_discussion','Ärendet återöppnades för fortsatt arbete.','2026-11-14 21:42:06'),(51,8,1,'admin','comment_added',NULL,'2026-11-14 22:01:03');
/*!40000 ALTER TABLE `ticket_history` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `tickets`
--

DROP TABLE IF EXISTS `tickets`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `tickets` (
  `id` int NOT NULL AUTO_INCREMENT,
  `type` varchar(20) NOT NULL,
  `title` varchar(180) NOT NULL,
  `description` text NOT NULL,
  `room_id` int DEFAULT NULL,
  `status` varchar(20) NOT NULL,
  `assigned_to` int DEFAULT NULL,
  `created_at` datetime NOT NULL,
  `completed_at` datetime DEFAULT NULL,
  `merged_into_id` int DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `room_id` (`room_id`),
  KEY `ix_tickets_assigned_to` (`assigned_to`),
  KEY `ix_tickets_status` (`status`),
  KEY `ix_ticket_status_assignee` (`status`,`assigned_to`),
  KEY `ix_tickets_merged_into_id` (`merged_into_id`),
  CONSTRAINT `fk_tickets_merged_into` FOREIGN KEY (`merged_into_id`) REFERENCES `tickets` (`id`),
  CONSTRAINT `tickets_ibfk_1` FOREIGN KEY (`room_id`) REFERENCES `rooms` (`id`),
  CONSTRAINT `tickets_ibfk_2` FOREIGN KEY (`assigned_to`) REFERENCES `users` (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=9 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `tickets`
--

LOCK TABLES `tickets` WRITE;
/*!40000 ALTER TABLE `tickets` DISABLE KEYS */;
INSERT INTO `tickets` VALUES (6,'fault','trasig lampa','lampan som hänger i taket är trasig behöver bytas',1,'in_progress',2,'2026-11-12 23:01:13',NULL,NULL),(7,'fault','trasig lampa','det är en trasig lamap i taket',1,'new',NULL,'2026-11-12 22:59:47',NULL,6),(8,'fault','skriver inte ut','printern ger mig vara spagetti',1,'in_progress',2,'2026-11-13 22:14:51',NULL,NULL);
/*!40000 ALTER TABLE `tickets` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `users`
--

DROP TABLE IF EXISTS `users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(80) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `role` varchar(20) NOT NULL,
  `discord_id` varchar(40) DEFAULT NULL,
  `active` tinyint(1) NOT NULL,
  `created_at` datetime NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `ix_users_username` (`username`),
  UNIQUE KEY `discord_id` (`discord_id`)
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `users`
--

LOCK TABLES `users` WRITE;
/*!40000 ALTER TABLE `users` DISABLE KEYS */;
INSERT INTO `users` VALUES (1,'admin','$argon2id$v=19$m=65536,t=3,p=4$YWxNCWFsDcFYC+Hc21vrfQ$FJqgVrJmSveWMAaR7UcFmKN8H7WuCaSwJJ+sjkcjK0s','admin',NULL,1,'2026-11-11 08:35:47'),(2,'labrat_1','$argon2id$v=19$m=65536,t=3,p=4$kZJSyjnHeO+9t5YSwrg3Bg$LlEjSkhi2569miggET6oQcdhS8nM4IcQ/TRmvxu6euc','worker',NULL,1,'2026-11-11 09:55:17');
/*!40000 ALTER TABLE `users` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Dumping routines for database 'roomtask'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-11-16 20:54:17
