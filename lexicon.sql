SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET time_zone = "+00:00";

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8 */;


CREATE TABLE IF NOT EXISTS `graph` (
  `id` int(11) NOT NULL,
  `word1` int(11) unsigned NOT NULL,
  `word2` int(11) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  KEY `word1` (`word1`),
  KEY `word2` (`word2`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_bin;

CREATE TABLE IF NOT EXISTS `words` (
  `id` int(10) unsigned NOT NULL AUTO_INCREMENT,
  `word` text COLLATE utf8_bin NOT NULL,
  `frequency` float unsigned NOT NULL,
  `length` tinyint(3) unsigned NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_bin AUTO_INCREMENT=1 ;


ALTER TABLE `graph`
  ADD CONSTRAINT `graph_ibfk_2` FOREIGN KEY (`word2`) REFERENCES `words` (`id`) ON DELETE CASCADE ON UPDATE CASCADE,
  ADD CONSTRAINT `graph_ibfk_1` FOREIGN KEY (`word1`) REFERENCES `words` (`id`) ON DELETE CASCADE ON UPDATE CASCADE;