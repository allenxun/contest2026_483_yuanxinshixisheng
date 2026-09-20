#ifndef CONFIG_EXAMPLES_K7RADIO_SHARED
static unsigned int g_prov_ap_count;
#endif
int main(void){
#ifndef CONFIG_EXAMPLES_K7RADIO_SHARED
return (int)g_prov_ap_count;
#else
return 0;
#endif
}
