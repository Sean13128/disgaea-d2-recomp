// Rasterize the actual editor/model against a copied real plaintext save.
// This checks CoreText layout; it is not a live Metal screenshot.
#define main af_model_test_main
#include "AF.editor-test.cpp"
#undef main
extern "C" void rsx_metal_overlay_raster(const SysOverlaySnapshot*,unsigned char*);
static void capture(const std::filesystem::path& folder,const char* label)
{
    display(true);SysOverlaySnapshot ui{};ps3_overlay_snapshot(&ui);
    std::vector<unsigned char> pixels(1280*720*4);rsx_metal_overlay_raster(&ui,pixels.data());
    std::ofstream out(folder/(std::string(label)+".ppm"),std::ios::binary);assert(out);
    out<<"P6\n1280 720\n255\n";
    for (unsigned i=0;i<1280*720;++i) {
        char rgb[]={char(pixels[i*4+2]),char(pixels[i*4+1]),char(pixels[i*4])};out.write(rgb,3);
    }
    close();
}
int main(int argc,char** argv)
{
    assert(argc==3);init();std::ifstream in(argv[1],std::ios::binary);assert(in);
    in.read(reinterpret_cast<char*>(memory.data()+root),1498152);assert(in.gcount()==1498152);
    party_count=vm_read16(root+0x1507ec);assert(validate(root));
    std::filesystem::path folder(argv[2]);std::filesystem::create_directories(folder);
    for (unsigned i=0;i<4;++i) {
        page=i;subpage=selected=0;const char* labels[]={"general","characters","items","presets"};capture(folder,labels[i]);
    }
    page=0;build_rows();selected=rows.size()-1;capture(folder,"toggles");
    page=1;unit=0;subpage=1;selected=0;capture(folder,"laharl");
    page=1;subpage=4;selected=0;capture(folder,"skills");
    page=1;subpage=2;selected=0;capture(folder,"equipment");
    page=2;item=0;subpage=1;selected=0;capture(folder,"item");
    page=0;subpage=0;selected=0;display(true);action(0x4000,0);close();
    editing=true;edit_field={"hl","HL",0x568,0,8,0,9999999999999ull,false};draft=vm_read64(root+0x568);step=1000000;selected=4;
    capture(folder,"edit-hl");
    puts("[AF-test] actual editor + real save, CoreText raster: PASS (Metal capture still requires host check)");
}
