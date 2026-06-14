using DanaSim.Viewer.Web.Controllers;
using FluentAssertions;
using Microsoft.AspNetCore.Mvc;

namespace DanaSim.Viewer.Web.Tests;

public class HomeControllerTests
{
    [Fact]
    public void Index_ReturnsViewResult()
    {
        var controller = new HomeController();

        var result = controller.Index();

        result.Should().BeOfType<ViewResult>();
    }
}
