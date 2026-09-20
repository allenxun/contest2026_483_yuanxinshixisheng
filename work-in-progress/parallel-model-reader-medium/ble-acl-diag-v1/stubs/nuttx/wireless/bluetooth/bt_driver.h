#include <stddef.h>
enum bt_buf_type_e { BT_CMD, BT_ACL_OUT, BT_EVT, BT_ACL_IN };
struct bt_driver_s { void *priv; int (*open)(struct bt_driver_s *); void (*close)(struct bt_driver_s *);
int (*send)(struct bt_driver_s *, enum bt_buf_type_e, void *, size_t);
int (*receive)(void); unsigned head_reserve; };
