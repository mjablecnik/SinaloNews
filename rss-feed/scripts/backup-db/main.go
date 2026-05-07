package main

import (
	"compress/gzip"
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/joho/godotenv"
)

func main() {
	// Accept project root as first argument, otherwise use cwd
	projectDir := ""
	outputDir := ""

	if len(os.Args) > 1 {
		projectDir = os.Args[1]
	} else {
		var err error
		projectDir, err = os.Getwd()
		if err != nil {
			fatal("failed to get working directory: %v", err)
		}
	}
	if len(os.Args) > 2 {
		outputDir = os.Args[2]
	}

	// Load .env from project root
	envPath := filepath.Join(projectDir, ".env")
	if err := godotenv.Load(envPath); err != nil {
		fatal("failed to load .env from %s: %v", envPath, err)
	}

	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		fatal("DATABASE_URL not set")
	}

	// Convert asyncpg URL to standard postgres URL
	dbURL = strings.Replace(dbURL, "postgresql+asyncpg://", "postgresql://", 1)

	// Output directory
	if outputDir == "" {
		outputDir = filepath.Join(projectDir, "backups")
	}
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		fatal("failed to create output dir: %v", err)
	}

	timestamp := time.Now().Format("20060102_150405")
	backupFile := filepath.Join(outputDir, fmt.Sprintf("backup_%s.sql.gz", timestamp))

	fmt.Printf("Connecting to database...\n")

	ctx := context.Background()
	conn, err := pgx.Connect(ctx, dbURL)
	if err != nil {
		fatal("failed to connect: %v", err)
	}
	defer conn.Close(ctx)

	// Get all table names
	rows, err := conn.Query(ctx, `
		SELECT tablename FROM pg_tables 
		WHERE schemaname = 'public' 
		ORDER BY tablename
	`)
	if err != nil {
		fatal("failed to list tables: %v", err)
	}

	var tables []string
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			fatal("failed to scan table name: %v", err)
		}
		tables = append(tables, name)
	}
	rows.Close()

	fmt.Printf("Found %d tables: %s\n", len(tables), strings.Join(tables, ", "))

	// Create output file
	f, err := os.Create(backupFile)
	if err != nil {
		fatal("failed to create backup file: %v", err)
	}
	defer f.Close()

	gz := gzip.NewWriter(f)
	defer gz.Close()

	// Write header
	write(gz, "-- Database backup created at %s\n", time.Now().Format(time.RFC3339))
	write(gz, "-- Tables: %s\n\n", strings.Join(tables, ", "))

	for _, table := range tables {
		fmt.Printf("  Dumping %s...\n", table)

		// Get CREATE TABLE statement via pg_dump-like approach
		// Get column definitions
		colRows, err := conn.Query(ctx, `
			SELECT column_name, data_type, is_nullable, column_default,
				   character_maximum_length
			FROM information_schema.columns 
			WHERE table_schema = 'public' AND table_name = $1
			ORDER BY ordinal_position
		`, table)
		if err != nil {
			fatal("failed to get columns for %s: %v", table, err)
		}

		write(gz, "-- Table: %s\n", table)
		write(gz, "DROP TABLE IF EXISTS %s CASCADE;\n", quoteIdent(table))
		write(gz, "CREATE TABLE %s (\n", quoteIdent(table))

		var cols []string
		var colNames []string
		first := true
		for colRows.Next() {
			var colName, dataType, isNullable string
			var colDefault *string
			var charMaxLen *int

			if err := colRows.Scan(&colName, &dataType, &isNullable, &colDefault, &charMaxLen); err != nil {
				fatal("failed to scan column: %v", err)
			}

			colNames = append(colNames, colName)
			colDef := fmt.Sprintf("  %s %s", quoteIdent(colName), pgType(dataType, charMaxLen))
			if isNullable == "NO" {
				colDef += " NOT NULL"
			}
			if colDefault != nil {
				colDef += fmt.Sprintf(" DEFAULT %s", *colDefault)
			}

			if !first {
				cols = append(cols, ",\n")
			}
			cols = append(cols, colDef)
			first = false
		}
		colRows.Close()

		for _, c := range cols {
			write(gz, "%s", c)
		}
		write(gz, "\n);\n\n")

		// Dump data
		copyRows, err := conn.Query(ctx, fmt.Sprintf("SELECT * FROM %s", quoteIdent(table)))
		if err != nil {
			fatal("failed to query %s: %v", table, err)
		}

		// Count rows and generate INSERT statements
		rowCount := 0
		fieldDescs := copyRows.FieldDescriptions()
		for copyRows.Next() {
			values, err := copyRows.Values()
			if err != nil {
				fatal("failed to get row values from %s: %v", table, err)
			}

			if rowCount == 0 {
				_ = fieldDescs // used for column names above
			}

			write(gz, "INSERT INTO %s (%s) VALUES (", quoteIdent(table), quoteIdentList(colNames))
			for i, val := range values {
				if i > 0 {
					write(gz, ", ")
				}
				write(gz, "%s", formatValue(val))
			}
			write(gz, ");\n")
			rowCount++
		}
		copyRows.Close()

		write(gz, "\n-- %d rows\n\n", rowCount)
	}

	// Dump sequences
	seqRows, err := conn.Query(ctx, `
		SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'
	`)
	if err == nil {
		for seqRows.Next() {
			var seqName string
			if err := seqRows.Scan(&seqName); err != nil {
				continue
			}
			var lastVal *int64
			err := conn.QueryRow(ctx, fmt.Sprintf("SELECT last_value FROM %s", quoteIdent(seqName))).Scan(&lastVal)
			if err == nil && lastVal != nil {
				write(gz, "SELECT setval('%s', %d);\n", seqName, *lastVal)
			}
		}
		seqRows.Close()
	}

	gz.Close()
	f.Close()

	info, _ := os.Stat(backupFile)
	fmt.Printf("Backup complete: %s (%s)\n", backupFile, formatSize(info.Size()))
}

func write(gz *gzip.Writer, format string, args ...any) {
	fmt.Fprintf(gz, format, args...)
}

func quoteIdent(s string) string {
	return fmt.Sprintf(`"%s"`, strings.ReplaceAll(s, `"`, `""`))
}

func quoteIdentList(names []string) string {
	quoted := make([]string, len(names))
	for i, n := range names {
		quoted[i] = quoteIdent(n)
	}
	return strings.Join(quoted, ", ")
}

func pgType(dataType string, charMaxLen *int) string {
	switch dataType {
	case "character varying":
		if charMaxLen != nil {
			return fmt.Sprintf("varchar(%d)", *charMaxLen)
		}
		return "varchar"
	case "integer":
		return "integer"
	case "bigint":
		return "bigint"
	case "text":
		return "text"
	case "boolean":
		return "boolean"
	case "timestamp without time zone":
		return "timestamp"
	case "timestamp with time zone":
		return "timestamptz"
	case "json":
		return "json"
	case "jsonb":
		return "jsonb"
	case "double precision":
		return "double precision"
	case "real":
		return "real"
	case "numeric":
		return "numeric"
	default:
		return dataType
	}
}

func formatValue(val any) string {
	if val == nil {
		return "NULL"
	}
	switch v := val.(type) {
	case string:
		return fmt.Sprintf("'%s'", strings.ReplaceAll(v, "'", "''"))
	case []byte:
		return fmt.Sprintf("'%s'", strings.ReplaceAll(string(v), "'", "''"))
	case time.Time:
		return fmt.Sprintf("'%s'", v.Format("2006-01-02 15:04:05"))
	case bool:
		if v {
			return "true"
		}
		return "false"
	case map[string]any:
		// JSON value - serialize it
		return fmt.Sprintf("'%s'", strings.ReplaceAll(fmt.Sprintf("%v", v), "'", "''"))
	default:
		return fmt.Sprintf("'%v'", val)
	}
}

func formatSize(bytes int64) string {
	if bytes < 1024 {
		return fmt.Sprintf("%d B", bytes)
	}
	if bytes < 1024*1024 {
		return fmt.Sprintf("%.1f KB", float64(bytes)/1024)
	}
	return fmt.Sprintf("%.1f MB", float64(bytes)/(1024*1024))
}

func fatal(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "Error: "+format+"\n", args...)
	os.Exit(1)
}
