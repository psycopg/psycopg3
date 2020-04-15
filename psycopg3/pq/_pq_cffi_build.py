#!/usr/bin/env python3
"""
Build the cffi-based pq wrapper (the psycopg3.pq._pq_cffi module).

This module can be executed from command line but it's also used automatically
by setup.py.

"""

# Copyright (C) 2020 The Psycopg Team

from cffi import FFI
import subprocess as sp

ffibuilder = FFI()

ffibuilder.cdef(
    """

/* structures and types */

typedef unsigned int Oid;
typedef struct pg_conn PGconn;
typedef struct pg_result PGresult;

typedef struct
{
    char   *keyword;
    char   *envvar;
    char   *compiled;
    char   *val;
    char   *label;
    char   *dispchar;
    int     dispsize;
} PQconninfoOption;

/* enums */

typedef enum
{
    PGRES_POLLING_FAILED = 0,
    PGRES_POLLING_READING,
    PGRES_POLLING_WRITING,
    PGRES_POLLING_OK,
    PGRES_POLLING_ACTIVE

} PostgresPollingStatusType;

typedef enum
{
    PQPING_OK,
    PQPING_REJECT,
    PQPING_NO_RESPONSE,
    PQPING_NO_ATTEMPT
} PGPing;

typedef enum
{
    CONNECTION_OK,
    CONNECTION_BAD,
    CONNECTION_STARTED,
    CONNECTION_MADE,
    CONNECTION_AWAITING_RESPONSE,
    CONNECTION_AUTH_OK,
    CONNECTION_SETENV,
    CONNECTION_SSL_STARTUP,
    CONNECTION_NEEDED,
    CONNECTION_CHECK_WRITABLE,
    CONNECTION_GSS_STARTUP
    /* CONNECTION_CHECK_TARGET PG 12 */
} ConnStatusType;

typedef enum
{
    PQTRANS_IDLE,
    PQTRANS_ACTIVE,
    PQTRANS_INTRANS,
    PQTRANS_INERROR,
    PQTRANS_UNKNOWN
} PGTransactionStatusType;

typedef enum
{
    PGRES_EMPTY_QUERY = 0,
    PGRES_COMMAND_OK,
    PGRES_TUPLES_OK,
    PGRES_COPY_OUT,
    PGRES_COPY_IN,
    PGRES_BAD_RESPONSE,
    PGRES_NONFATAL_ERROR,
    PGRES_FATAL_ERROR,
    PGRES_COPY_BOTH,
    PGRES_SINGLE_TUPLE
} ExecStatusType;

int PQlibVersion(void);

/* 33.1. Database Connection Control Functions */
PGconn *PQconnectdb(const char *conninfo);
PGconn *PQconnectStart(const char *conninfo);
PostgresPollingStatusType PQconnectPoll(PGconn *conn);
PQconninfoOption *PQconndefaults(void);
PQconninfoOption *PQconninfo(PGconn *conn);
PQconninfoOption *PQconninfoParse(const char *conninfo, char **errmsg);
void PQfinish(PGconn *conn);
void PQreset(PGconn *conn);
int PQresetStart(PGconn *conn);
PostgresPollingStatusType PQresetPoll(PGconn *conn);
PGPing PQping(const char *conninfo);

/* 33.2. Connection Status Functions */
char *PQdb(const PGconn *conn);
char *PQuser(const PGconn *conn);
char *PQpass(const PGconn *conn);
char *PQhost(const PGconn *conn);
// char *PQhostaddr(const PGconn *conn); TODO: conditional, only libpq>=12
char *PQport(const PGconn *conn);
char *PQtty(const PGconn *conn);
char *PQoptions(const PGconn *conn);
ConnStatusType PQstatus(const PGconn *conn);
PGTransactionStatusType PQtransactionStatus(const PGconn *conn);
const char *PQparameterStatus(const PGconn *conn, const char *paramName);
int PQprotocolVersion(const PGconn *conn);
int PQserverVersion(const PGconn *conn);
char *PQerrorMessage(const PGconn *conn);
int PQsocket(const PGconn *conn);
int PQbackendPID(const PGconn *conn);
int PQconnectionNeedsPassword(const PGconn *conn);
int PQconnectionUsedPassword(const PGconn *conn);
int PQsslInUse(PGconn *conn);   /* TODO: const in PG 12 docs - verify/report */
/* TODO: PQsslAttribute, PQsslAttributeNames, PQsslStruct, PQgetssl */

/* 33.3. Command Execution Functions */
PGresult *PQexec(PGconn *conn, const char *command);
PGresult *PQexecParams(PGconn *conn,
                       const char *command,
                       int nParams,
                       const Oid *paramTypes,
                       const char * const *paramValues,
                       const int *paramLengths,
                       const int *paramFormats,
                       int resultFormat);
PGresult *PQprepare(PGconn *conn,
                    const char *stmtName,
                    const char *query,
                    int nParams,
                    const Oid *paramTypes);
PGresult *PQexecPrepared(PGconn *conn,
                         const char *stmtName,
                         int nParams,
                         const char * const *paramValues,
                         const int *paramLengths,
                         const int *paramFormats,
                         int resultFormat);
PGresult *PQdescribePrepared(PGconn *conn, const char *stmtName);
PGresult *PQdescribePortal(PGconn *conn, const char *portalName);
ExecStatusType PQresultStatus(const PGresult *res);
/* PQresStatus: not needed, we have pretty enums */
char *PQresultErrorMessage(const PGresult *res);
/* TODO: PQresultVerboseErrorMessage */
char *PQresultErrorField(const PGresult *res, int fieldcode);
void PQclear(PGresult *res);

/* 33.3.2. Retrieving Query Result Information */
int PQntuples(const PGresult *res);
int PQnfields(const PGresult *res);
char *PQfname(const PGresult *res, int column_number);
int PQfnumber(const PGresult *res, const char *column_name);
Oid PQftable(const PGresult *res, int column_number);
int PQftablecol(const PGresult *res, int column_number);
int PQfformat(const PGresult *res, int column_number);
Oid PQftype(const PGresult *res, int column_number);
int PQfmod(const PGresult *res, int column_number);
int PQfsize(const PGresult *res, int column_number);
int PQbinaryTuples(const PGresult *res);
char *PQgetvalue(const PGresult *res, int row_number, int column_number);
int PQgetisnull(const PGresult *res, int row_number, int column_number);
int PQgetlength(const PGresult *res, int row_number, int column_number);
int PQnparams(const PGresult *res);
Oid PQparamtype(const PGresult *res, int param_number);
/* PQprint: pretty useless */

/* 33.3.3. Retrieving Other Result Information */
char *PQcmdStatus(PGresult *res);
char *PQcmdTuples(PGresult *res);
Oid PQoidValue(const PGresult *res);

/* 33.3.4. Escaping Strings for Inclusion in SQL Commands */
/* TODO: PQescapeLiteral PQescapeIdentifier PQescapeStringConn PQescapeString */
unsigned char *PQescapeByteaConn(PGconn *conn,
                                 const unsigned char *from,
                                 size_t from_length,
                                 size_t *to_length);
unsigned char *PQescapeBytea(const unsigned char *from,
                             size_t from_length,
                             size_t *to_length);
unsigned char *PQunescapeBytea(const unsigned char *from, size_t *to_length);


/* 33.4. Asynchronous Command Processing */
int PQsendQuery(PGconn *conn, const char *command);
int PQsendQueryParams(PGconn *conn,
                      const char *command,
                      int nParams,
                      const Oid *paramTypes,
                      const char * const *paramValues,
                      const int *paramLengths,
                      const int *paramFormats,
                      int resultFormat);
int PQsendPrepare(PGconn *conn,
                  const char *stmtName,
                  const char *query,
                  int nParams,
                  const Oid *paramTypes);
int PQsendQueryPrepared(PGconn *conn,
                        const char *stmtName,
                        int nParams,
                        const char * const *paramValues,
                        const int *paramLengths,
                        const int *paramFormats,
                        int resultFormat);
int PQsendDescribePrepared(PGconn *conn, const char *stmtName);
int PQsendDescribePortal(PGconn *conn, const char *portalName);
PGresult *PQgetResult(PGconn *conn);
int PQconsumeInput(PGconn *conn);
int PQisBusy(PGconn *conn);
int PQsetnonblocking(PGconn *conn, int arg);
int PQisnonblocking(const PGconn *conn);
int PQflush(PGconn *conn);

/* 33.11. Miscellaneous Functions */
void PQfreemem(void *ptr);
void PQconninfoFree(PQconninfoOption *connOptions);
PGresult *PQmakeEmptyPGresult(PGconn *conn, ExecStatusType status);

/* Optimized functions */
const char *pg3_get_value(const PGresult *result,
                          int row, int column, int *length);
"""
)


def get_from_pg_config(what: str) -> str:
    out = sp.run(["pg_config", f"--{what}"], stdout=sp.PIPE, check=True)
    return out.stdout.strip().decode("utf8")


includedir = get_from_pg_config("includedir")

ffibuilder.set_source(
    "psycopg3.pq._pq_cffi",
    """
#include <libpq-fe.h>

const char *
pg3_get_value(const PGresult *result, int row, int column, int *length)
{
    if ((*length = PQgetlength(result, row, column))) {
        return PQgetvalue(result, row, column);
    }
    else {
        if (PQgetisnull(result, row, column))
            return NULL;
        else
            return "";
    }
}
    """,
    include_dirs=[includedir],
    libraries=["pq"],
)

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
