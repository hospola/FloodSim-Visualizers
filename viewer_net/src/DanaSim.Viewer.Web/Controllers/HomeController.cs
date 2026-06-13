using Microsoft.AspNetCore.Mvc;

namespace DanaSim.Viewer.Web.Controllers;

public sealed class HomeController : Controller
{
    public IActionResult Index() => View();
}
